---
name: threat-model
description: Defensive security analysis of a system, service, or change — asset and trust-boundary mapping, structured threat enumeration, detection-as-code, and a prioritized hardening roadmap. Use for authorized security review, threat modeling, detection engineering, or hardening. Defensive only.
---

Produce a defender's analysis: understand how something could be attacked so it can
be protected and monitored. This skill is for **authorized** review and hardening.
It does not produce working exploits, weaponized payloads, or operational
attack tooling — it stays at the level of threat patterns, detection, and defense.

## When to trigger

- "Threat-model this", "security review of…", "what's the attack surface of…",
  "write detections for…", "harden this against attackers".

## Method

1. **Scope & assets.** What system/change is in scope, what's worth protecting
   (data, capabilities, trust), and the assumed attacker. Call `recall` for prior
   security notes on the system.
2. **Trust boundaries.** Map where data/control crosses a boundary (network, process,
   privilege, supply chain). Boundaries are where threats live.
3. **Threat enumeration.** Walk categories (spoofing, tampering, repudiation, info
   disclosure, denial of service, elevation of privilege) against each boundary.
   Describe the threat at the pattern level — the mechanism, not a runnable exploit.
4. **Prioritization.** Rank by likelihood × impact so effort goes where it matters.
5. **Detection-as-code.** For the top threats, give concrete detection logic —
   log signatures, query/rule sketches, invariants to alert on — that a defender
   can implement.
6. **Hardening roadmap.** Mitigations ordered by leverage: what to fix now, next,
   and what residual risk remains and must be accepted or monitored.

## Output

Assets → boundaries → ranked threats → detections → hardening roadmap → residual
risk. Offer to `sidecar_store` the threat model for reuse. If a request crosses
from defense into building a working exploit, say so and keep the response
defensive.
