"""The shared pre-branding entry for complete Windows candidate preparation."""

RELEASE_INTEGRATIONS_ANCHOR = "        if not args.dev:\n            # Substitute domains\n"
RELEASE_INTEGRATIONS_STEP = (
    "        # Apply reviewed Windows integrations before product-name substitution.\n"
    "        from scripts.apply_windows_arc_workflow import (\n"
    "            ROOT as arcium_integration_root, integrate, integrate_bundle)\n"
    "        integrate_bundle(source_tree, apply=True)\n"
    "        integrate(source_tree, patch=arcium_integration_root /\n"
    "                  'patches/windows/mac-window-buttons.patch', apply=True)\n\n"
)


def inject_release_integrations(builder: str) -> str:
    """Reject an unknown builder before changing or downloading Chromium."""
    if builder.count(RELEASE_INTEGRATIONS_ANCHOR) != 1:
        raise ValueError("Unknown Windows pre-branding integration entry")
    return builder.replace(RELEASE_INTEGRATIONS_ANCHOR,
                           RELEASE_INTEGRATIONS_STEP + RELEASE_INTEGRATIONS_ANCHOR, 1)
