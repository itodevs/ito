# Externalize pilot-facing UI text

Pilot-facing UI text is loaded from JSON resource files using an i18next-style structure. UI components should reference message keys rather than hardcoding labels, status messages, menu text, or session-state copy.

Driver- or server-provided display strings, such as availability details or Session Termination Reasons, may be either resource keys or free text. The Pilot Client first attempts to resolve such values through its localization resources and falls back to displaying the supplied text as-is.

Robot names are proper names supplied by the driver and are displayed as-is. Enum-style labels controlled by Ito, such as Robot Type and Robot Status, are localized through resource files.

V1 ships one default resource set. The resource structure should leave room for future localization and themed language variants, but v1 does not implement language/theme selection.

This adds small upfront structure to the VR client, but it prevents hardcoded strings from spreading through the product surface. It keeps future localization feasible and allows later themed language variants without rewriting UI components.
