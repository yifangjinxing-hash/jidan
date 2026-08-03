# Security policy

Jidan is an experimental agent runtime. Do not use it for sensitive production data, unattended financial activity, health decisions, or safety-critical control.

## Financial handoff boundary

The experimental Alipay adapter may only open a host-pinned Android front door from an explicit foreground Jidan submit. That submit is the user's decision for this low-risk `NAVIGATION` action; the Host must not ask the same “open this app?” question again. The adapter must not receive, prefill, or transmit an account, recipient, amount, QR payload, payment URL, order token, password, verification code, or biometric instruction. It must not use private URI schemes, Accessibility, coordinate taps, OCR-driven control, or automatic retries after an ambiguous launch.

`handoff_opened` proves only that the pinned package and allowed foreground component were observed in the controlled ADB lab. It never means that a payment screen was reached or a payment was attempted, committed, settled, or verified. Payment truth must come from the payment provider's official authorization and server-side verification path.

Do not copy a certificate digest or component name from an untrusted installation into a host manifest and treat that as verification. Version, signer, launcher, and foreground allowlists are local trust policy and must be reviewed from an independent trusted source. A changed manifest requires a new capability digest and a new Grant.

ADB, the Java executable, and the `apksigner` JAR are part of the Lab Host's trusted computing base. Use reviewed vendor-supplied tools and protect their local files; the harness cannot defend against a replaced toolchain, a compromised Host, or a compromised Android device.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability reporting for this repository:

<https://github.com/yifangjinxing-hash/jidan/security/advisories/new>

Include the affected commit, Android/Python versions, a minimal reproduction, expected impact, and whether the reproduction performs a real external action.

## Supported versions

Only the latest commit on the default branch receives security fixes during the prototype stage.
