# Reuse and attribution

## spending-effort-with-jev — MIT

Source: [Yaxin9Luo/spending-effort-with-jev](https://github.com/Yaxin9Luo/spending-effort-with-jev).
Inspected commit: `8aef59d72e932d362d5b404ed839290f04db3bb0`.
Original file: [hooks/judge.ts](https://github.com/Yaxin9Luo/spending-effort-with-jev/blob/8aef59d72e932d362d5b404ed839290f04db3bb0/plugins/spending-effort-with-jev/hooks/judge.ts).

`src/auto_effort/context.py` ports the `GO_AHEADS` and `isGoAhead` helper to Python.
It retains a bare confirmation locally when no caller-supplied task context exists.
The original copyright notice and MIT license are included in
`licenses/spending-effort-with-jev.MIT.txt` and distributed with the package.

We also adopt the distinction between a new message and the previous reply being
answered, using a bounded `previous_reply` supplied by the host. The original's
Claude mod, UI, adaptive threshold tuning, transcript scraping, and automatic max
recommendations are not dependencies of this package.

## Jev Auto Router — Apache-2.0 design reference

Source: [miniLV/Jev-Auto-Router](https://github.com/miniLV/Jev-Auto-Router).
Inspected commit: `ff76b00fb18d0d64016a6a5d8f162875569a7894`.
References: [policy-guard.ts](https://github.com/miniLV/Jev-Auto-Router/blob/ff76b00fb18d0d64016a6a5d8f162875569a7894/src/policy-guard.ts),
[routing-policy.md](https://github.com/miniLV/Jev-Auto-Router/blob/ff76b00fb18d0d64016a6a5d8f162875569a7894/skills/jev-auto-router/references/routing-policy.md).

We adopt these architecture patterns with our own implementation: off/shadow/auto
modes, exact capability membership, explicit fallback handling, and applying only
the native effort setting. No source code from this repository is included. Its
model-routing proxy, authenticated caller, native streaming/cancellation pipeline,
and deployment framework remain outside this effort-selector package.

## Provider SDKs

Optional `typesafe-sdk` and `openrouter` dependencies are used through their public
interfaces and retain their own licenses. They own the provider wire format. The
monorepo continues to use its registered Jev CLI for real fleet API requests.
